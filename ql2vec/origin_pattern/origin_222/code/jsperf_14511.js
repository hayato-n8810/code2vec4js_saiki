var VAR_1 = {
  KEY_1: "",
  KEY_2: true,
  KEY_3: 5,
  KEY_4: 123.123,
  KEY_5: [],
  KEY_6: {},
};
var VAR_2 = 0;
for (key in VAR_1) {
  if (VAR_1.hasOwnProperty(key)) VAR_2++;
}
