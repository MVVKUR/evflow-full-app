export const REQUIRED_KWH_MIN = 0.1;
export const REQUIRED_KWH_MAX = 150;

export function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function validatePassword(value: string) {
  if (!value) {
    return 'Password is required.';
  }

  if (value.length < 8) {
    return 'Password must be at least 8 characters.';
  }

  return null;
}

export function validateRequiredKWh(value: string | number) {
  const numeric = typeof value === 'number' ? value : Number(String(value).trim());

  if (String(value).trim() === '' || !Number.isFinite(numeric)) {
    return `Enter a number from ${REQUIRED_KWH_MIN} to ${REQUIRED_KWH_MAX} kWh.`;
  }

  if (numeric <= 0) {
    return 'Required energy must be greater than 0 kWh.';
  }

  if (numeric < REQUIRED_KWH_MIN || numeric > REQUIRED_KWH_MAX) {
    return `Required energy must be between ${REQUIRED_KWH_MIN} and ${REQUIRED_KWH_MAX} kWh.`;
  }

  return null;
}

export function validateWalletBalance(balanceIdr: number | null, totalDueIdr: number) {
  if (balanceIdr === null || !Number.isFinite(balanceIdr)) {
    return 'Wallet balance is unavailable. Please try again.';
  }

  if (totalDueIdr > balanceIdr) {
    return 'Insufficient wallet balance. Please top up before paying.';
  }

  return null;
}

export function formatCurrencyIDR(amount: number) {
  return `Rp ${Math.abs(amount).toLocaleString('id-ID')}`;
}

export function formatChargingDuration(minutes: number | null) {
  if (minutes === null || !Number.isFinite(minutes) || minutes <= 0 || minutes > 24 * 60) {
    return null;
  }

  const roundedMinutes = Math.round(minutes);
  if (roundedMinutes < 60) {
    return `${roundedMinutes} min`;
  }

  const hours = Math.floor(roundedMinutes / 60);
  const remainingMinutes = roundedMinutes % 60;

  return remainingMinutes > 0 ? `${hours} hr ${remainingMinutes} min` : `${hours} hr`;
}

export function getEstimatedChargingMinutes(requiredKWh: number, chargerPowerKW: number | null | undefined) {
  if (!Number.isFinite(requiredKWh) || requiredKWh <= 0 || !chargerPowerKW || !Number.isFinite(chargerPowerKW) || chargerPowerKW <= 0) {
    return null;
  }

  return (requiredKWh / chargerPowerKW) * 60;
}

export function formatTransactionDate(isoDate: string, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Jakarta',
    ...options
  }).format(new Date(isoDate));
}
