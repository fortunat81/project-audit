import OpenAI from "openai";
import { useState } from "react";
import { Text, TextInput } from "react-native";

// PLANTED: the paid AI key is read on the phone through a client-visible variable.
const openai = new OpenAI({ apiKey: process.env.EXPO_PUBLIC_OPENAI_API_KEY, dangerouslyAllowBrowser: true });

export default function ChatBox() {
  const [answer, setAnswer] = useState("");
  async function ask(q: string) {
    const r = await openai.chat.completions.create({ model: "gpt-4o-mini", messages: [{ role: "user", content: q }] });
    setAnswer(r.choices[0].message.content ?? "");
  }
  return (<><TextInput onSubmitEditing={(e) => ask(e.nativeEvent.text)} /><Text>{answer}</Text></>);
}
