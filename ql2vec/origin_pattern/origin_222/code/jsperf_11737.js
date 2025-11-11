VAR_1 = {
  KEY_1: "abc",
  KEY_2: "def",
  KEY_3: "ghi",
  KEY_4: "jkl",
  KEY_5: "mno",
  KEY_6: "pqr",
  KEY_7: "stu",
  KEY_8: "vwx",
  KEY_9: "yz",
};
function FUNCTION_1() {}
FUNCTION_1.VAR_2 = {
  KEY_10: "abc",
  KEY_11: "def",
  KEY_12: "ghi",
  KEY_13: "jkl",
  KEY_14: "mno",
  KEY_15: "pqr",
  KEY_16: "stu",
  KEY_17: "vwx",
  KEY_18: "yz",
};
var VAR_3 = new FUNCTION_1();
var VAR_4 = "";
for (key in VAR_3) {
  if (VAR_3.hasOwnProperty(key)) {
    VAR_4 = VAR_4 + VAR_3[key];
  }
}
