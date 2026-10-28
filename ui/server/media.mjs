// Safari requests byte ranges even for local HEVC-with-alpha movies.
export function mediaRange(header, size) {
  if (!header) return null;
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!match || (!match[1] && !match[2])) return { invalid: true };
  let start, end;
  if (!match[1]) { start = Math.max(0, size - Number(match[2])); end = size - 1; }
  else { start = Number(match[1]); end = match[2] ? Math.min(Number(match[2]), size - 1) : size - 1; }
  return !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start >= size || end < start ? { invalid: true } : { start, end };
}
