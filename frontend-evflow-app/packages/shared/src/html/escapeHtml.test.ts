import { describe, it, expect } from 'vitest';

import { escapeHtml } from './escapeHtml';

describe('escapeHtml', () => {
  it('escapes the ampersand entity', () => {
    expect(escapeHtml('Tom & Jerry')).toBe('Tom &amp; Jerry');
  });

  it('escapes the less-than entity', () => {
    expect(escapeHtml('a < b')).toBe('a &lt; b');
  });

  it('escapes the greater-than entity', () => {
    expect(escapeHtml('a > b')).toBe('a &gt; b');
  });

  it('escapes the double-quote entity', () => {
    expect(escapeHtml('say "hi"')).toBe('say &quot;hi&quot;');
  });

  it('escapes the single-quote entity', () => {
    expect(escapeHtml("it's")).toBe('it&#39;s');
  });

  it('escapes all five entities together, including a script payload', () => {
    expect(escapeHtml(`<script>alert('x&y')</script>`)).toBe(
      '&lt;script&gt;alert(&#39;x&amp;y&#39;)&lt;/script&gt;'
    );
  });

  it('passes plaintext through unchanged', () => {
    expect(escapeHtml('Jalan Sudirman 123')).toBe('Jalan Sudirman 123');
  });

  it('returns an empty string unchanged', () => {
    expect(escapeHtml('')).toBe('');
  });
});
