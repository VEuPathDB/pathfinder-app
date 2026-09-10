FROM node:24-alpine AS base

# Enable Corepack so Yarn 4 is available
RUN corepack enable

# Install dependencies only when needed
FROM base AS deps
# The install clones `@veupathdb/assistant-client` from its repository.
RUN apk add --no-cache libc6-compat git
WORKDIR /app

# Workspace config; Corepack provides Yarn 4 via the packageManager field.
COPY package.json yarn.lock .yarnrc.yml ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared-ts/package.json ./packages/shared-ts/

# Cache mount keeps yarn's download cache across builds.
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn \
    yarn install --immutable

# Workspace source + generated shared-ts types (gitignored), shared by dev + builder.
FROM base AS sources
WORKDIR /app
COPY --from=deps /app ./
COPY apps/web ./apps/web
COPY packages/shared-ts ./packages/shared-ts
COPY packages/spec ./packages/spec
RUN yarn --cwd packages/shared-ts generate

FROM sources AS dev
WORKDIR /app/apps/web

ENV NODE_ENV=development
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/').then(r => r.ok ? r.text() : Promise.reject(new Error(r.status))).then(() => process.exit(0), () => process.exit(1))"

CMD ["yarn", "next", "dev", "-p", "3000", "-H", "0.0.0.0"]

FROM sources AS builder
WORKDIR /app/apps/web

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# next.config.js rewrites resolve at build time; inside Docker the API is http://api:8000.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN yarn build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/apps/web/public ./apps/web/public

# Set the correct permission for prerender cache
RUN mkdir -p /app/apps/web/.next
RUN chown nextjs:nodejs /app/apps/web/.next

# Automatically leverage output traces to reduce image size
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Warms the Node module cache on the first "/" render so the first real user
# request doesn't pay the ~10s cold SSR cost. start-period gives the container
# room to boot Node and finish the cold render; subsequent checks take <1s.
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/').then(r => r.ok ? r.text() : Promise.reject(new Error(r.status))).then(() => process.exit(0), () => process.exit(1))"

CMD ["node", "apps/web/server.js"]

