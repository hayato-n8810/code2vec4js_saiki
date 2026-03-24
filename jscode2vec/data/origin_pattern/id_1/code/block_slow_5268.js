for (var VAR_3 in VAR_1) {
  if (VAR_1[VAR_3] == "(") VAR_2++;
  if (VAR_1[VAR_3] == ")" && --VAR_2 < 0) return false;
}
