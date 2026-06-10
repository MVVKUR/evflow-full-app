import { EVFLOW_API_BASE_URL } from '../stations/api';

export type RegisterRequest = {
  username: string;
  password: string;
  full_name?: string | null;
  ev_model_id?: string | null;
  main_connector_type?: string | null;
  location_consent?: boolean;
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type UserPublic = {
  id: string;
  username: string | null;
  full_name: string | null;
  email: string | null;
  account_type: string;
  ev_model_id: string | null;
  main_connector_type: string | null;
  location_consent: boolean;
  profile_completed: boolean;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: UserPublic;
};

export class AuthApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'AuthApiError';
    this.status = status;
  }
}

export function register(request: RegisterRequest, fetcher: typeof fetch = fetch) {
  return postAuth('/api/v1/auth/register', request, 201, fetcher);
}

export function login(request: LoginRequest, fetcher: typeof fetch = fetch) {
  return postAuth('/api/v1/auth/login', request, 200, fetcher);
}

async function postAuth(path: string, body: RegisterRequest | LoginRequest, expectedStatus: number, fetcher: typeof fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}${path}`, {
    body: JSON.stringify(body),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  if (response.status !== expectedStatus) {
    throw new AuthApiError(response.status, await getAuthErrorMessage(response));
  }

  return response.json() as Promise<TokenResponse>;
}

async function getAuthErrorMessage(response: Response) {
  const fallback = getFallbackAuthErrorMessage(response.status);

  try {
    const payload = await response.json();
    const detail = payload?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail)) {
      const firstMessage = detail
        .map((item) => item?.msg)
        .find((message): message is string => typeof message === 'string' && Boolean(message));

      return firstMessage ?? fallback;
    }
  } catch {
    // Keep the status-specific fallback below.
  }

  return fallback;
}

function getFallbackAuthErrorMessage(status: number) {
  if (status === 401) {
    return 'Username or password is incorrect.';
  }

  if (status === 409) {
    return 'Username is already taken.';
  }

  if (status === 422) {
    return 'Please check the highlighted fields and try again.';
  }

  return 'Authentication request failed. Please try again.';
}
