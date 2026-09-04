/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { sanitizeHtml } from "./sanitizeHtml";

describe("sanitizeHtml", () => {
  // ── Allowed tags pass through ──────────────────────────────

  it("keeps allowed inline tags unchanged", () => {
    const input = "<b>bold</b> <i>italic</i> <em>emphasis</em>";
    const result = sanitizeHtml(input);
    expect(result).toContain("<b>bold</b>");
    expect(result).toContain("<i>italic</i>");
    expect(result).toContain("<em>emphasis</em>");
  });

  it("keeps <strong>, <span>, <sub>, <sup>, <br> tags", () => {
    const input = "<strong>s</strong><span>p</span><sub>b</sub><sup>p</sup><br>";
    const result = sanitizeHtml(input);
    expect(result).toContain("<strong>s</strong>");
    expect(result).toContain("<span>p</span>");
    expect(result).toContain("<sub>b</sub>");
    expect(result).toContain("<sup>p</sup>");
    expect(result).toContain("<br>");
  });

  it("keeps <a> tags with safe href", () => {
    const input = '<a href="https://example.com">link</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain("href=");
    expect(result).toContain("https://example.com");
  });

  it("keeps <img> tags with safe src", () => {
    const input = '<img src="https://example.com/img.png">';
    const result = sanitizeHtml(input);
    expect(result).toContain("<img");
    expect(result).toContain("https://example.com/img.png");
  });

  // ── Disallowed tags are stripped ───────────────────────────

  it("strips <script> tags but keeps inner text", () => {
    const input = "<script>alert('xss')</script>safe text";
    const result = sanitizeHtml(input);
    expect(result).not.toContain("<script");
    expect(result).toContain("safe text");
  });

  it("strips <div> tags but keeps content", () => {
    const input = "<div>wrapped content</div>";
    const result = sanitizeHtml(input);
    expect(result).not.toContain("<div");
    expect(result).toContain("wrapped content");
  });

  it("strips <style> tags", () => {
    const input = "<style>body{color:red}</style>text";
    const result = sanitizeHtml(input);
    expect(result).not.toContain("<style");
  });

  it("strips <iframe> tags", () => {
    const input = '<iframe src="https://evil.com"></iframe>ok';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("<iframe");
    expect(result).toContain("ok");
  });

  it("strips <form> tags but keeps content", () => {
    const input = "<form>content</form>";
    const result = sanitizeHtml(input);
    expect(result).not.toContain("<form");
    expect(result).toContain("content");
  });

  // ── Event handler attributes are removed ───────────────────

  it("removes onclick attributes from allowed tags", () => {
    const input = '<b onclick="alert(1)">bold</b>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("onclick");
    expect(result).toContain("<b>");
    expect(result).toContain("bold");
  });

  it("removes onmouseover and other on* attributes", () => {
    const input = '<span onmouseover="hack()">hover</span>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("onmouseover");
  });

  it("removes onerror from img tags", () => {
    const input = '<img src="https://example.com/x.png" onerror="alert(1)">';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("onerror");
  });

  // ── Style attributes are removed ──────────────────────────

  it("removes style attributes from allowed tags", () => {
    const input = '<span style="color:red">styled</span>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("style=");
    expect(result).toContain("styled");
  });

  // ── Unsafe URLs are removed ────────────────────────────────

  it("removes javascript: href from <a> tags", () => {
    const input = '<a href="javascript:alert(1)">click</a>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("javascript:");
    expect(result).toContain("click");
  });

  it("removes data: href from <a> tags", () => {
    const input = '<a href="data:text/html,<script>alert(1)</script>">link</a>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain('href="data:');
  });

  it("removes javascript: src from <img> tags", () => {
    const input = '<img src="javascript:void(0)">';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("javascript:");
  });

  it("allows relative URLs (starting with /)", () => {
    const input = '<a href="/about">about</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain('href="/about"');
  });

  it("allows anchor URLs (starting with #)", () => {
    const input = '<a href="#section">section</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain('href="#section"');
  });

  it("allows mailto: URLs", () => {
    const input = '<a href="mailto:test@example.com">email</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain("mailto:test@example.com");
  });

  // ── <a> tags get target and rel attributes ─────────────────

  it("adds target=_blank and rel=noopener noreferrer to <a> tags", () => {
    const input = '<a href="https://example.com">link</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain('target="_blank"');
    expect(result).toContain('rel="noopener noreferrer"');
  });

  it("overrides existing target on <a> tags", () => {
    const input = '<a href="https://example.com" target="_self">link</a>';
    const result = sanitizeHtml(input);
    expect(result).toContain('target="_blank"');
  });

  // ── Nested / complex cases ─────────────────────────────────

  it("handles nested allowed tags", () => {
    const input = "<b><i>bold italic</i></b>";
    const result = sanitizeHtml(input);
    expect(result).toContain("<b><i>bold italic</i></b>");
  });

  it("handles disallowed tags nested inside allowed tags", () => {
    const input = "<b><div>inner</div></b>";
    const result = sanitizeHtml(input);
    expect(result).toContain("<b>");
    expect(result).not.toContain("<div");
    expect(result).toContain("inner");
  });

  it("handles plain text without HTML", () => {
    const input = "just plain text";
    const result = sanitizeHtml(input);
    expect(result).toBe("just plain text");
  });

  it("handles empty string", () => {
    const result = sanitizeHtml("");
    expect(result).toBe("");
  });

  it("handles HTML entities correctly", () => {
    const input = "&amp; &lt; &gt;";
    const result = sanitizeHtml(input);
    // DOMParser decodes entities then innerHTML re-encodes them
    expect(result).toContain("&amp;");
    expect(result).toContain("&lt;");
    expect(result).toContain("&gt;");
  });

  it("strips multiple event handlers from a single element", () => {
    const input = '<span onclick="a()" onmouseover="b()" onfocus="c()">text</span>';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("onclick");
    expect(result).not.toContain("onmouseover");
    expect(result).not.toContain("onfocus");
    expect(result).toContain("text");
  });
});
