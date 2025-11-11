var VAR_1 = Array(10);
var VAR_2;
for (var VAR_3 in VAR_1) {
  if (!Object.hasOwnProperty(VAR_3, VAR_1)) continue;
  VAR_2 = VAR_1[VAR_3];
}
