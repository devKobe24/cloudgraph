// Exact decimal arithmetic. The Python estimator uses Decimal with ROUND_HALF_UP;
// float would drift (0.0225 * 730 is 16.424999999999997 in JS, which rounds to
// 16.42 while Python gives 16.43). BigInt at a fixed scale keeps the two equal.

const SCALE = 1_000_000n; // six decimal places
const SCALE_DIGITS = 6n;

export function scaled(value: string | number): bigint {
  const text = typeof value === "number" ? value.toFixed(Number(SCALE_DIGITS)) : value.trim();
  const negative = text.startsWith("-");
  const body = negative ? text.slice(1) : text;
  const [whole, frac = ""] = body.split(".");
  const padded = (frac + "000000").slice(0, Number(SCALE_DIGITS));
  const result = BigInt(whole || "0") * SCALE + BigInt(padded || "0");
  return negative ? -result : result;
}

function roundHalfUp(numerator: bigint, divisor: bigint): bigint {
  // Every quantity in this domain is non-negative, so half-up is a plain compare.
  const quotient = numerator / divisor;
  const remainder = numerator % divisor;
  return remainder * 2n >= divisor ? quotient + 1n : quotient;
}

/** rate x factors, rounded to cents exactly once -- same as Python's to_money(). */
export function componentCents(rate: string, factors: (number | string)[]): bigint {
  let numerator = scaled(rate);
  for (const factor of factors) numerator *= scaled(factor);
  const exponent = SCALE_DIGITS * BigInt(factors.length + 1) - 2n;
  return roundHalfUp(numerator, 10n ** exponent);
}

export function formatCents(cents: bigint): string {
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  const whole = abs / 100n;
  const rest = (abs % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole}.${rest}`;
}
