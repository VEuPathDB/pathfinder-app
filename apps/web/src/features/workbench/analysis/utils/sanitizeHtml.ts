/**
 * Sanitize HTML to only allow safe inline tags, removing scripts,
 * event handlers, unsafe URLs, and style attributes.
 *
 * Allowed tags: a, b, i, em, strong, span, br, sub, sup, img
 */

const ALLOWED_TAGS = new Set([
  "a",
  "b",
  "i",
  "em",
  "strong",
  "span",
  "br",
  "sub",
  "sup",
  "img",
]);

const SAFE_URL_PATTERN = /^(https?:\/\/|\/|#|mailto:)/i;

export function sanitizeHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");

  function walk(node: Node) {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as Element;
        if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) {
          el.replaceWith(...Array.from(el.childNodes));
        } else {
          for (const attr of Array.from(el.attributes)) {
            if (attr.name.startsWith("on") || attr.name === "style") {
              el.removeAttribute(attr.name);
            }
            if (
              (attr.name === "href" || attr.name === "src") &&
              !SAFE_URL_PATTERN.test(attr.value.trim())
            ) {
              el.removeAttribute(attr.name);
            }
          }
          if (el.tagName === "A") {
            el.setAttribute("target", "_blank");
            el.setAttribute("rel", "noopener noreferrer");
          }
          walk(el);
        }
      }
    }
  }

  walk(doc.body);
  return doc.body.innerHTML;
}
