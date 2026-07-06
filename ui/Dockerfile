FROM node:22-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (including devDependencies for build)
RUN npm install

# Copy source code
COPY . .

RUN npm run build

ARG VITE_API_URL
ENV VITE_API_URL=${API_URL}

# Start server
CMD ["npm", "run", "preview"]