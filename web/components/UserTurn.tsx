import { motion } from "framer-motion";

export function UserTurn({ question }: { question: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex justify-end"
    >
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-[15px] leading-relaxed text-white">
        {question}
      </div>
    </motion.div>
  );
}
