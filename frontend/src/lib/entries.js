// One saved question and answer, as the saved-conversation and shared-conversation APIs return it, in the shape the UI renders.
export function fromHistory(m) {
  const extra = m.extra || {};
  return {
    id: `log-${m.id}`,
    logId: m.id,
    question: m.question,
    answer: m.answer,
    citations: extra.citations || [],
    followups: extra.followups || [],
    safety: extra.safety || null,
    abstained: !!extra.abstained,
    feedback: m.user_feedback,
    state: "done",
  };
}
