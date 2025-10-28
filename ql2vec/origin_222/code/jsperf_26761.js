var VAR_1 = {
  KEY_1: "1",
  KEY_2: "2",
  KEY_3: "3",
  KEY_4: "{}",
  KEY_5: "5",
};
function FUNCTION_1(VAR_2) {
  for (var VAR_3 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_3)) {
      return true;
    }
  }
  return false;
}
FUNCTION_1(VAR_1);
