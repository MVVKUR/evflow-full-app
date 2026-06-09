export type ApiClientOptions = {
  baseUrl: string;
  fetcher?: typeof fetch;
};

export function createApiClient({ baseUrl, fetcher = fetch }: ApiClientOptions) {
  async function get<T>(path: string): Promise<T> {
    const response = await fetcher(`${baseUrl}${path}`);

    if (!response.ok) {
      throw new Error(`EVFlow API request failed with status ${response.status}`);
    }

    return response.json() as Promise<T>;
  }

  return { get };
}

type QueryParamValue = string | number | boolean;

export function toQueryString(params: Record<string, QueryParamValue | QueryParamValue[] | null | undefined>) {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== '') {
          query.append(key, String(item));
        }
      });
      return;
    }

    query.set(key, String(value));
  });

  const queryString = query.toString();
  return queryString ? `?${queryString}` : '';
}
