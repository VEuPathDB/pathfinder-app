import type { ParamSpec } from "@/features/strategy/parameters/spec";
import type { VocabOption, VocabNode } from "@/lib/utils/vocab";

export type ParamFieldApi = {
  state: {
    value: string | string[];
    meta: {
      errors: unknown[];
      isDirty: boolean;
      isTouched: boolean;
    };
  };
  handleChange: (value: string | string[]) => void;
  handleBlur: () => void;
};

export type ParamWidgetProps = {
  spec: ParamSpec;
  name: string;
  options: VocabOption[];
  vocabTree: VocabNode[] | null;
  field: ParamFieldApi;
  disabled?: boolean;
};
