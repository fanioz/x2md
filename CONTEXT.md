# x2md — Domain glossary

This file captures the language of the x2md project. It is a glossary, not a spec: it records what each term means so the codebase and UI stay consistent.

## Core domain

- **X / Twitter URL**: A web address pointing to a post, thread, or article on x.com or twitter.com. The tool accepts several host variants, query strings, fragments, and bare numeric IDs.

- **Post**: A single tweet or X post.

- **Self-thread**: A sequence of connected posts by the same author. The tool can enumerate the full thread when the provider supports it.

- **Article**: A long-form X Article (formerly Twitter Article). Rendered differently from a post because its content is stored as Draft.js blocks.

- **Target**: The parsed result of a user-supplied URL or ID. Contains the status ID and optional handle.

- **Document**: The normalised internal representation of the converted content. A Document has a kind (`post`, `thread`, or `article`), an author, a list of posts, optional warnings, and metadata such as the source URL and provider used.

- **Provider**: A retrieval strategy that fetches the raw content from a third-party endpoint and converts it into a Document. Providers are tried in order until one succeeds.

- **Author**: The person who wrote the post, thread, or article. Contains a handle, name, and avatar URL.

- **Media**: Images, videos, or GIFs attached to a post. Rendered as Markdown links.

- **Poll**: An Twitter/X poll attached to a post. Rendered as a list of choices with vote counts.

- **Quote**: A post embedded inside another post. Rendered as a nested blockquote.

- **Facet**: A span inside post text that carries extra meaning, such as a mention, hashtag, or URL. Facets are used to turn plain text into Markdown links and formatting.

## Web app domain

- **Visitor**: A person using the web app.

- **Conversion**: The action of submitting a URL or ID to the web app and receiving Markdown back.

- **Markdown output**: The final text the visitor copies or downloads. It includes YAML front matter followed by the rendered body.

- **Warnings**: Non-fatal messages about the conversion, such as a provider being unable to enumerate a full thread. Shown in the UI but do not block the result.

- **Provider name**: The provider that ultimately produced the Document, exposed in the web app so a visitor can see which strategy succeeded.
