FROM node:22-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (including devDependencies for build)
RUN npm install

# Copy source code
COPY . .

ARG API_URL
ENV VITE_API_URL=$API_URL

RUN npm run build

# Start server
CMD ["npm", "run", "preview"]