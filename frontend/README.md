This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Local n8n Webhook Tunneling (ngrok)

To test n8n webhooks locally and stream social analytics directly into PostgreSQL:

1. Start the Next.js development server:
   ```bash
   npm run dev
   ```

2. In a separate terminal window, start the ngrok tunnel:
   ```bash
   npm run tunnel
   # (runs: ngrok http 3000)
   ```

3. Copy the generated forwarding URL (e.g., `https://[id].ngrok-free.app`).

4. In your n8n workflow HTTP Request node:
   - **Method**: `POST`
   - **URL**: Replace `http://localhost:3000` with:
     ```
     https://[id].ngrok-free.app/api/webhooks/n8n/social-analytics
     ```
   - **Headers**:
     ```
     Authorization: Bearer agile_n8n_secret_2026
     Content-Type: application/json
     ```
   - **Body**: Send an array of Facebook and Instagram post objects.

When n8n executes, data will be parsed and atomically upserted directly into the local PostgreSQL `posts` and `post_analytics` tables.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
