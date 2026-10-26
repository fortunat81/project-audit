export default async function Page() {
  const res = await fetch("https://example.com/api/chat", { method: "POST" });
  const aiHtml = await res.text();
  // PLANTED: AI output rendered as raw HTML.
  return <div dangerouslySetInnerHTML={{ __html: aiHtml }} />;
}
