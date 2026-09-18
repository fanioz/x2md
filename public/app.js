/**
 * x2md web app frontend.
 *
 * Sends a URL to /api/convert and displays the returned Markdown.
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

  let currentFilename = 'post.md';

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

  function downloadFile(text, filename) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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
    downloadFile(outputEl.value, currentFilename);
  });
})();
