var VAR_1 = [],
  VAR_2 = 5000;
while (VAR_2--) {
  VAR_1[VAR_2 - 1] = VAR_2;
}
var FUNCTION_1 = function (VAR_3) {
  VAR_3 = VAR_3;
};
for (var VAR_4 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_4)) {
    FUNCTION_1(VAR_1[VAR_4]);
  }
}
