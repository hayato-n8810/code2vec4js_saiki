var VAR_1 = {
  KEY_1: "toto",
  KEY_2: "titi",
  KEY_3: "tutu",
  KEY_4: "tete",
};
var VAR_2;
for (value in VAR_1) {
  if (VAR_1.hasOwnProperty(value)) {
    VAR_2 = value;
  }
}
