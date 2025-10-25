export default function Message() {
  const name = "yahya";
  if (!name) return <h3>hello</h3>;
  return <h3>hello world {name}</h3>;
}
