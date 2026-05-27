FROM node:20-alpine
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# Vendored local tarball for @platform/monitoring-ui (file: dep); must be present
# before install so the frozen lockfile's file: entry resolves inside the build.
COPY vendor/ ./vendor/
RUN pnpm install --frozen-lockfile
COPY . .
EXPOSE 5173
CMD ["pnpm", "run", "dev", "--", "--host", "0.0.0.0"]
