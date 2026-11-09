export function focusComposer(): void {
  const input = document.querySelector<HTMLTextAreaElement>("[data-composer-input]");
  if (input === null) return;
  input.focus({ preventScroll: true });
  input.setSelectionRange(input.value.length, input.value.length);
}
