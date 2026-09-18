/**
 * x2md web app frontend.
 *
 * Sends a URL to /api/convert and displays the returned Markdown plus
 * downloadable media (images and videos).
 */

(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);

  const form = $('#convert-form');
  const urlInput = $('#url');
  const submitBtn = $('#submit');
  const statusEl = $('#status');
  const resultSection = $('#result');
  const outputEl = $('#output');
  const copyBtn = $('#copy');
  const downloadBtn = $('#download');
  const metaEl = $('#meta');
  const mediaSection = $('#media');
  const mediaList = $('#media-list');
  const mediaTitle = $('#media-title');
  const downloadAllBtn = $('#download-all');

  let currentFilename = 'post.md';
  let currentMedia = [];

  function setStatus(message, type = 'info') {
    statusEl.textContent = message;
    statusEl.hidden = !message;
    statusEl.className = `status status--${type}`;
  }

  function clearStatus() {
    setStatus('', 'info');
    statusEl.hidden = true;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatMeta(meta) {
    const parts = [];
    if (meta.kind) parts.push(`Kind: <strong>${escapeHtml(meta.kind)}</strong>`);
    if (meta.provider) parts.push(`Provider: ${escapeHtml(meta.provider)}`);
    if (meta.handle) parts.push(`By: @${escapeHtml(meta.handle)}`);
    if (meta.id) parts.push(`ID: ${escapeHtml(meta.id)}`);
    return parts.join(' · ');
  }

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      // Fallback for older browsers / insecure contexts.
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        return true;
      } catch (_) {
        return false;
      } finally {
        document.body.removeChild(textarea);
      }
    }
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function downloadText(text, filename) {
    downloadBlob(new Blob([text], { type: 'text/markdown;charset=utf-8' }), filename);
  }

  function downloadUrl(href, filename) {
    const a = document.createElement('a');
    a.href = href;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function renderMedia(media) {
    currentMedia = media || [];
    mediaList.innerHTML = '';
    if (!currentMedia.length) {
      mediaSection.hidden = true;
      return;
    }
    mediaTitle.textContent = `Media (${currentMedia.length})`;
    currentMedia.forEach((item) => {
      const li = document.createElement('li');
      li.className = 'media-item';

      const label = document.createElement('span');
      label.className = 'media-label';
      const kindLabel = item.kind === 'image' ? 'Image' : (item.kind === 'gif' ? 'GIF' : 'Video');
      label.textContent = item.alt ? `${kindLabel}: ${item.alt}` : kindLabel;

      const button = document.createElement('button');
      button.className = 'button-secondary media-dl';
      button.type = 'button';
      button.textContent = 'Download';
      button.addEventListener('click', () => downloadUrl(item.download_url, item.filename));

      li.appendChild(label);
      li.appendChild(button);
      mediaList.appendChild(li);
    });
    mediaSection.hidden = false;
  }

  async function downloadAllAsZip() {
    if (typeof JSZip === 'undefined') {
      setStatus('ZIP library failed to load. Use the per-item Download buttons.', 'error');
      return;
    }
    if (!currentMedia.length) return;

    const originalText = downloadAllBtn.textContent;
    downloadAllBtn.disabled = true;
    downloadAllBtn.textContent = 'Preparing ZIP…';
    setStatus('Fetching media…', 'info');

    const zip = new JSZip();
    let failed = 0;

    for (const item of currentMedia) {
      try {
        const resp = await fetch(item.download_url, { mode: 'cors' });
        if (!resp.ok) {
          failed += 1;
          continue;
        }
        const blob = await resp.blob();
        zip.file(item.filename, blob);
      } catch (err) {
        failed += 1;
      }
    }

    if (Object.keys(zip.files).length === 0) {
      setStatus('Could not fetch any media files.', 'error');
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = originalText;
      return;
    }

    try {
      const content = await zip.generateAsync({ type: 'blob' });
      const zipName = (currentFilename.replace(/\.md$/, '') || 'post') + '_media.zip';
      downloadBlob(content, zipName);
      if (failed > 0) {
        setStatus(`${Object.keys(zip.files).length} file(s) zipped; ${failed} could not be fetched.`, 'success');
      } else {
        setStatus(`Downloaded ${Object.keys(zip.files).length} file(s) as ZIP.`, 'success');
      }
    } catch (err) {
      setStatus('Failed to build ZIP archive.', 'error');
    } finally {
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = originalText;
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const url = urlInput.value.trim();
    if (!url) {
      setStatus('Please enter a URL or post ID.', 'error');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Converting…';
    clearStatus();
    resultSection.hidden = true;
    outputEl.value = '';
    metaEl.innerHTML = '';
    renderMedia([]);

    try {
      const response = await fetch('/api/convert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });

      let data;
      try {
        data = await response.json();
      } catch (parseErr) {
        setStatus('Received an unexpected response from the server.', 'error');
        return;
      }

      if (!response.ok) {
        setStatus(data.error || `Error ${response.status}`, 'error');
        return;
      }

      outputEl.value = data.markdown || '';
      currentFilename = data.meta?.filename || 'post.md';
      metaEl.innerHTML = data.meta ? formatMeta(data.meta) : '';

      if (data.meta?.warnings?.length) {
        const warnings = data.meta.warnings
          .map((w) => escapeHtml(String(w)))
          .join('<br>');
        metaEl.innerHTML += `<div class="warnings">${warnings}</div>`;
      }

      renderMedia(data.media);

      resultSection.hidden = false;
      outputEl.focus();
    } catch (err) {
      setStatus('Network error. Please try again.', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Convert';
    }
  });

  copyBtn.addEventListener('click', async () => {
    const ok = await copyToClipboard(outputEl.value);
    setStatus(ok ? 'Copied to clipboard.' : 'Could not copy.', ok ? 'success' : 'error');
  });

  downloadBtn.addEventListener('click', () => {
    downloadText(outputEl.value, currentFilename);
  });

  downloadAllBtn.addEventListener('click', downloadAllAsZip);
})();
