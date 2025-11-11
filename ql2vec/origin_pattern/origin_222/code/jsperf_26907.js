var VAR_1 = {
  KEY_1: 123,
  KEY_2: "test",
  KEY_3: true,
};
var VAR_2 = 0,
  VAR_3;
for (VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) VAR_2++;
}
