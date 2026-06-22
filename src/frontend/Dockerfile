# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY src/frontend/package*.json ./

# Install dependencies
RUN npm ci --legacy-peer-deps

# Copy source code
COPY src/frontend .

# Build Next.js app
RUN npm run build

# Runtime stage
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY src/frontend/package*.json ./

# Install production dependencies only
RUN npm ci --legacy-peer-deps --only=production

# Copy built app from builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

# Expose port
EXPOSE 3000

# Start the app
CMD ["npm", "start"]
