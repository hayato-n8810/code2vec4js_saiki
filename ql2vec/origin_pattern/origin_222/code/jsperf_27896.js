var VAR_1 = {
  KEY_1: "beep",
  KEY_2: "boop",
  KEY_3: "foo",
  KEY_4: "bar",
  KEY_5: "hello",
};
function FUNCTION_1(VAR_2) {
  return VAR_1[VAR_2];
}
for (var VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) {
    FUNCTION_1(VAR_3);
  }
}
