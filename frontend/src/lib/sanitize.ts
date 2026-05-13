import DOMPurify from "dompurify";

/**
 * Sanitize untrusted HTML before insertion via dangerouslySetInnerHTML
 * or before rendering markdown-derived HTML from research artifacts.
 *
 * Use for: research results, LLM-rendered markdown, scraped snippets.
 * Do NOT use for: user-submitted strings (sanitized server-side already).
 */
export const safe = (html: string): string => DOMPurify.sanitize(html);
