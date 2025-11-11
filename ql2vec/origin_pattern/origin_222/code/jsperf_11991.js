function FUNCTION_1(VAR_1) {
  return VAR_1 * 42;
}
var VAR_2 = [11 / 6, 5, 10, 15];
for (var VAR_3 in VAR_2) {
  if (!VAR_2.hasOwnProperty(VAR_3)) continue;
  FUNCTION_1(VAR_2[VAR_3]);
}
