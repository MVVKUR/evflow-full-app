import { describe, expect, it } from 'vitest';
import { selectedSpkluMarkerSvg, spkluMarkerSvg } from './spkluMarkerSvg';

describe('spkluMarkerSvg', () => {
  it('draws the badge at the requested size', () => {
    expect(spkluMarkerSvg(32)).toContain('width="32" height="32"');
  });

  it('carries no availability dot when no colour is given', () => {
    // A station whose live counts are unknown must look neutral. Painting a dot
    // anyway would state an availability we do not have.
    expect(spkluMarkerSvg(32)).not.toContain('cx="400"');
  });

  it('adds the availability dot when a colour is given', () => {
    const svg = spkluMarkerSvg(32, '#D64545');
    expect(svg).toContain('fill="#D64545"');
    expect(svg).toContain('cx="400"');
  });

  it('rings the dot in white so it reads on both ends of the gradient', () => {
    const svg = spkluMarkerSvg(32, '#10A957');
    expect(svg.indexOf('r="104" fill="#ffffff"')).toBeLessThan(svg.indexOf('fill="#10A957"'));
  });

  it('keeps the selected marker distinguishable and still colourable', () => {
    const selected = selectedSpkluMarkerSvg(44, '#F0B429');
    expect(selected).toContain('width="44" height="44"');
    expect(selected).toContain('stroke="#00565F"');
    expect(selected).toContain('fill="#F0B429"');
  });

  it('gives the two badges different gradient ids so one cannot bleed into the other', () => {
    expect(spkluMarkerSvg(32)).toContain('evflowSpkluGradient"');
    expect(selectedSpkluMarkerSvg(44)).toContain('evflowSpkluGradientSelected');
  });
});
