# frontend/Dockerfile
FROM node:20-alpine

WORKDIR /app

# Install deps first for better Docker layer caching
COPY package.json package-lock.json* ./
RUN npm install

# Copy source
COPY . .

EXPOSE 5173

# Run Vite dev server inside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
