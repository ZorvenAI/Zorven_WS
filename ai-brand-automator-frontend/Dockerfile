# Node.js base image
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Build arguments for Next.js public env vars (needed at build time)
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy project files (invalidates cache when source changes)
COPY . .

# Build the application with env vars available
ARG CACHEBUST=1
RUN echo "Building with NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL (cachebust=$CACHEBUST)" && npm run build

# Expose port
EXPOSE 3000

# Start the application
CMD ["npm", "start"]
