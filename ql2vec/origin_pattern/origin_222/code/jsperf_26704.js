function FUNCTION_1(VAR_1) {
  for (const VAR_2 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_2)) {
      return false;
    }
  }
  return true;
}
var VAR_3 = {};
var VAR_4 = {
  KEY_1: "John",
  KEY_2: "Doe",
  KEY_3: 50,
  KEY_4: "blue",
};
FUNCTION_1(VAR_4);
