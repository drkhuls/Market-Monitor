export function formatPrice(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatSigned(value: number, digits = 2): string {
  const text = Math.abs(value).toFixed(digits);
  if (value > 0) return `+${text}`;
  if (value < 0) return `−${text}`;
  return text;
}

export function formatPercent(value: number): string {
  const text = Math.abs(value).toFixed(2);
  if (value > 0) return `+${text}%`;
  if (value < 0) return `−${text}%`;
  return `${text}%`;
}

export function formatPercent1(value: number): string {
  return `${value.toFixed(1)}%`;
}
