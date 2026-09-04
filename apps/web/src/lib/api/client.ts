import {
  APIError,
  buildUrl,
  extractErrorMessage,
  getAuthHeaders,
  parseResponseBody,
} from "./http";

type HttpMethod =
  | "GET"
  | "POST"
  | "PUT"
  | "PATCH"
  | "DELETE"
  | "get"
  | "post"
  | "put"
  | "patch"
  | "delete";

type QueryParams = {
  [key: string]: unknown;
};

export type RequestConfig<D = unknown> = {
  method: HttpMethod;
  url: string;
  params?: QueryParams | undefined;
  data?: D | undefined;
  headers?: Record<string, string> | undefined;
  signal?: AbortSignal | undefined;
};

export type ResponseConfig<T = unknown> = {
  data: T;
  status: number;
  statusText: string;
  headers: Headers;
};

export type ResponseErrorConfig<E = unknown> = APIError & { data: E };

export type Client = <TData = unknown, _TError = unknown, TVariables = unknown>(
  config: RequestConfig<TVariables>,
) => Promise<ResponseConfig<TData>>;

export async function client<TData = unknown, _TError = unknown, TVariables = unknown>(
  cfg: RequestConfig<TVariables>,
): Promise<ResponseConfig<TData>> {
  const url = buildUrl(cfg.url, cfg.params);
  const hasBody = cfg.data !== undefined;
  const init: RequestInit = {
    method: cfg.method.toUpperCase(),
    headers: {
      ...getAuthHeaders({
        accept: "application/json",
        ...(hasBody ? { contentType: "application/json" } : {}),
      }),
      ...(cfg.headers ?? {}),
    },
    credentials: "include",
  };
  if (hasBody) {
    init.body = JSON.stringify(cfg.data);
  }
  if (cfg.signal !== undefined) {
    init.signal = cfg.signal;
  }
  const resp = await fetch(url, init);
  const data = await parseResponseBody(resp);
  if (!resp.ok) {
    const msg = extractErrorMessage(data) ?? `HTTP ${resp.status} ${resp.statusText}`;
    throw new APIError(msg, {
      status: resp.status,
      statusText: resp.statusText,
      url,
      data,
    });
  }
  return {
    data: data as TData,
    status: resp.status,
    statusText: resp.statusText,
    headers: resp.headers,
  };
}

export default client;
