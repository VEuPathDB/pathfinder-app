import { createStore } from "./middleware";

interface PhoneBarState {
  slot: HTMLElement | null;
  setSlot: (slot: HTMLElement | null) => void;
}

export const usePhoneBarStore = createStore<PhoneBarState>("PhoneBarStore", (set) => ({
  slot: null,
  setSlot: (slot) => set((s) => (s.slot === slot ? s : { slot })),
}));
