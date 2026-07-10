export default function Alert({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="text-sm text-red-700 bg-red-50 border border-red-100 rounded-xl px-4 py-3 mb-4">
      {message}
    </p>
  );
}
