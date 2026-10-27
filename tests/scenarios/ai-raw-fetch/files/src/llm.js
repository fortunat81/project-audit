// Calls an AI provider with a plain HTTP request: there is no SDK in package.json.
export async function ask(prompt) {
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "some/model", messages: [{ role: "user", content: prompt }] }),
  });
  return res.json();
}
