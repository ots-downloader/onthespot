# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
ARG API_URL
ENV VITE_API_URL=$API_URL
RUN npm run build

# Production stage
FROM node:22-alpine AS runner

WORKDIR /app

# Copy only the production dependencies and the build output
# Note: Adjust the path if 'dist' is not the correct build directory
COPY --from=builder /app/package*.json ./
RUN npm install --production

COPY --from=builder /app/dist ./dist

# Expose the port (default Vite preview port is 4173, but check your config)
EXPOSE 4173

# Start the server
CMD ["npm", "run", "preview"]
