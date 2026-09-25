import { useForm } from "@tanstack/react-form";
import {
  DEFAULT_COLOCATION,
  type ColocationFormValues,
} from "../schema/colocationSchema";

export function useColocationForm(initialValues?: Partial<ColocationFormValues>) {
  const defaults: ColocationFormValues = { ...DEFAULT_COLOCATION, ...initialValues };
  return useForm({
    defaultValues: defaults,
    onSubmit: () => {},
  });
}

export type ColocationForm = ReturnType<typeof useColocationForm>;
