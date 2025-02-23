# Use Node.js base image
FROM node:18

# Set working directory
WORKDIR /app

# Copy frontend files
COPY . .

# Install dependencies
RUN npm install

# Expose frontend port
EXPOSE 5173

# Run the frontend app
CMD ["npm", "run", "dev"]
