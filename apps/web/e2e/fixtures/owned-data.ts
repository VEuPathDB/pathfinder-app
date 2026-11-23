import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
  Request,
} from "@playwright/test";

import {
  CSRF_HEADERS,
  type ConversationRow,
  deleted,
  geneSetListUrls,
  listBody,
} from "./api-client";

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

const BEGUN = new RegExp(`/api/v1/conversations/(${UUID})/begin$`);

const MADE_BY_RESPONSE = [
  new RegExp(`/api/v1/conversations$`),
  new RegExp(`/api/v1/conversations/open$`),
  new RegExp(`/api/v1/conversations/${UUID}/(fork|restore|duplicate)$`),
  new RegExp(`/api/v1/shared/[^/]+/copy$`),
];

const GENE_SET_IMPORT = /\/api\/v1\/gene-sets\/import$/;

const CHAT = /\/api\/v1\/chat$/;

interface MadeBody {
  id?: string;
  conversationId?: string;
}

interface GeneSetRow {
  id: string;
  wdkStrategyId?: number | null;
}

interface OwnedRow extends ConversationRow {
  geneSetId?: string | null;
}

function pathOf(url: string): string {
  return new URL(url).pathname;
}

function parsed(text: string | null | undefined): unknown {
  if (text == null || text === "") return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export class OwnedData {
  private readonly conversations = new Set<string>();
  private readonly geneSets = new Set<string>();
  private readonly pending: Promise<void>[] = [];

  private noteRequest(method: string, url: string, body: unknown): void {
    if (method !== "POST") return;
    const path = pathOf(url);
    const begun = BEGUN.exec(path);
    if (begun?.[1] !== undefined) this.conversations.add(begun[1]);
    if (CHAT.test(path) && body !== null && typeof body === "object") {
      const chat = body as MadeBody;
      for (const id of [chat.id, chat.conversationId]) {
        if (id !== undefined && new RegExp(`^${UUID}$`).test(id)) {
          this.conversations.add(id);
        }
      }
    }
  }

  private noteMade(method: string, url: string, status: number, body: unknown): void {
    if (method !== "POST" || status < 200 || status >= 300) return;
    if (body === null || typeof body !== "object") return;
    const made = body as MadeBody;
    const path = pathOf(url);
    if (MADE_BY_RESPONSE.some((pattern) => pattern.test(path))) {
      const id = made.conversationId ?? made.id;
      if (id !== undefined) this.conversations.add(id);
    }
    if (GENE_SET_IMPORT.test(path) && made.id !== undefined) {
      this.geneSets.add(made.id);
    }
  }

  private wantsBody(method: string, url: string): boolean {
    if (method !== "POST") return false;
    const path = pathOf(url);
    return GENE_SET_IMPORT.test(path) || MADE_BY_RESPONSE.some((p) => p.test(path));
  }

  watchPages(context: BrowserContext): void {
    context.on("request", (request: Request) => {
      this.noteRequest(request.method(), request.url(), parsed(request.postData()));
    });
    context.on("requestfinished", (request: Request) => {
      if (!this.wantsBody(request.method(), request.url())) return;
      this.pending.push(
        (async () => {
          const response = await request.response();
          if (response === null) return;
          const text = await response.text().catch(() => null);
          this.noteMade(
            request.method(),
            request.url(),
            response.status(),
            parsed(text),
          );
        })(),
      );
    });
  }

  track(api: APIRequestContext): APIRequestContext {
    const post = async (
      url: string,
      options?: Parameters<APIRequestContext["post"]>[1],
    ): Promise<APIResponse> => {
      const response = await api.post(url, options);
      await this.noteApi("POST", response, options?.data);
      return response;
    };
    const fetch = async (
      urlOrRequest: Parameters<APIRequestContext["fetch"]>[0],
      options?: Parameters<APIRequestContext["fetch"]>[1],
    ): Promise<APIResponse> => {
      const response = await api.fetch(urlOrRequest, options);
      const method = (options?.method ?? "GET").toUpperCase();
      await this.noteApi(method, response, options?.data);
      return response;
    };
    return new Proxy(api, {
      get(target, property, receiver) {
        if (property === "post") return post;
        if (property === "fetch") return fetch;
        const value: unknown = Reflect.get(target, property, receiver);
        if (typeof value !== "function") return value;
        const method = value as (...args: unknown[]) => unknown;
        return method.bind(target);
      },
    });
  }

  private async noteApi(method: string, response: APIResponse, data: unknown) {
    const body = typeof data === "string" ? parsed(data) : (data ?? null);
    this.noteRequest(method, response.url(), body);
    if (!this.wantsBody(method, response.url())) return;
    const text = await response.text().catch(() => null);
    this.noteMade(method, response.url(), response.status(), parsed(text));
  }

  async deleteAll(req: APIRequestContext, baseURL: string): Promise<void> {
    await Promise.allSettled(this.pending);
    const rows: OwnedRow[] = [];
    for (const path of ["/api/v1/conversations", "/api/v1/conversations/dismissed"]) {
      const listed = await listBody<OwnedRow>(await req.get(`${baseURL}${path}`), path);
      rows.push(...listed.filter((row) => this.conversations.has(row.id)));
    }
    const strategyIds = new Set(rows.map((row) => row.wdkStrategyId));
    for (const row of rows) {
      if (row.geneSetId != null) this.geneSets.add(row.geneSetId);
    }
    for (const url of geneSetListUrls(baseURL)) {
      for (const set of await listBody<GeneSetRow>(await req.get(url), url)) {
        if (set.wdkStrategyId != null && strategyIds.has(set.wdkStrategyId)) {
          this.geneSets.add(set.id);
        }
      }
    }
    await Promise.all(
      [...this.geneSets].map(async (id) =>
        deleted(
          await req.delete(`${baseURL}/api/v1/gene-sets/${id}`, {
            headers: CSRF_HEADERS,
          }),
          `gene set ${id}`,
        ),
      ),
    );
    for (const saved of [false, true]) {
      await Promise.all(
        rows
          .filter((row) => (row.isSaved === true) === saved)
          .map(async (row) =>
            deleted(
              await req.delete(
                `${baseURL}/api/v1/conversations/${row.id}?deleteFromWdk=true`,
                { headers: CSRF_HEADERS, timeout: 120_000 },
              ),
              `conversation ${row.id}`,
            ),
          ),
      );
    }
  }
}
