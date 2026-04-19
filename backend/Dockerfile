FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* .npmrc* ./
RUN npm install --legacy-peer-deps

COPY tsconfig*.json nest-cli.json ./
COPY src ./src
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json /app/package-lock.json* /app/.npmrc* ./
RUN npm install --omit=dev --legacy-peer-deps && npm cache clean --force

COPY --from=builder /app/dist ./dist

ENV PORT=3001
EXPOSE 3001

CMD ["node", "dist/main.js"]
