function FUNCTION_1(VAR_1) {
  for (var VAR_2 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_2)) {
      return false;
    }
  }
  return true;
}
var VAR_3,
  VAR_4 = "test",
  VAR_5 = {},
  VAR_6 = { KEY_1: "test" },
  VAR_7 = "hi";
if (!FUNCTION_1(VAR_4)) {
  console.log(VAR_7);
}
