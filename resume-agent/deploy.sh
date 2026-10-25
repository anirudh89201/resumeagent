args=()
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  echo "Adding: $line"
  args+=(--env "$line")
done < .env

MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" agentcore deploy "${args[@]}"