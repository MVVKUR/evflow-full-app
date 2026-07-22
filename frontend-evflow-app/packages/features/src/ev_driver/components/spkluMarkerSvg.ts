// Circular SPKLU map badge: white charging-station glyph (screen + bolt cut out,
// cable to plug) on the brand green→blue gradient, traced from the supplied
// charging-station artwork. Gradient stops sampled from the source PNG.

const GRADIENT_TOP = '#64C08A';
const GRADIENT_BOTTOM = '#049FF6';

function badgeInner(gradientId: string) {
  return (
    `<defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="${GRADIENT_TOP}"/>` +
    `<stop offset="1" stop-color="${GRADIENT_BOTTOM}"/>` +
    `</linearGradient></defs>` +
    `<circle cx="256" cy="256" r="256" fill="url(#${gradientId})"/>` +
    // Station body with the screen slot and lightning bolt cut out (even-odd).
    `<path fill="#ffffff" fill-rule="evenodd" d="` +
    `M150 122 h132 a28 28 0 0 1 28 28 v212 a28 28 0 0 1 -28 28 h-132 a28 28 0 0 1 -28 -28 v-212 a28 28 0 0 1 28 -28 Z ` +
    `M156 152 h120 a6 6 0 0 1 6 6 v26 a6 6 0 0 1 -6 6 h-120 a6 6 0 0 1 -6 -6 v-26 a6 6 0 0 1 6 -6 Z ` +
    `M243 232 L178 316 h34 l-16 62 66 -86 h-35 Z"/>` +
    // Cable: out of the body's upper right, rounded corner, down to the plug.
    `<path fill="none" stroke="#ffffff" stroke-width="26" stroke-linecap="round" d="M306 196 h48 q14 0 14 14 v66"/>` +
    // Plug head + two prongs.
    `<path fill="#ffffff" d="M340 276 h56 a16 16 0 0 1 16 16 v28 a12 12 0 0 1 -12 12 h-64 a12 12 0 0 1 -12 -12 v-28 a16 16 0 0 1 16 -16 Z"/>` +
    `<rect fill="#ffffff" x="346" y="332" width="14" height="30" rx="7"/>` +
    `<rect fill="#ffffff" x="376" y="332" width="14" height="30" rx="7"/>`
  );
}

/** Default SPKLU marker: the gradient badge at `size` px (square). */
export function spkluMarkerSvg(size: number) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="${size}" height="${size}" style="display:block">` +
    badgeInner('evflowSpkluGradient') +
    `</svg>`
  );
}

/** Selected SPKLU marker: same badge with a dark ring + white gap so the tapped station stands out. */
export function selectedSpkluMarkerSvg(size: number) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-44 -44 600 600" width="${size}" height="${size}" style="display:block">` +
    `<circle cx="256" cy="256" r="286" fill="none" stroke="#00565F" stroke-width="24"/>` +
    `<circle cx="256" cy="256" r="266" fill="none" stroke="#ffffff" stroke-width="20"/>` +
    badgeInner('evflowSpkluGradientSelected') +
    `</svg>`
  );
}
