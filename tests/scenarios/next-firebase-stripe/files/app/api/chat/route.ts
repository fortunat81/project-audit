import OpenAI from "openai";
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
// PLANTED: public AI endpoint with no login, no rate limit, no max_tokens.
export async function POST(req: Request) {
  const { message } = await req.json();
  const r = await openai.chat.completions.create({ model: "gpt-4o-mini", messages: [{ role: "user", content: message }] });
  return new Response(r.choices[0].message.content);
}
