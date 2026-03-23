for (var VAR_5 in VAR_3)
  if (VAR_3.hasOwnProperty(VAR_5)) {
    VAR_4.push(
      encodeURIComponent(VAR_5) + "=" + encodeURIComponent(VAR_3[VAR_5]),
    );
  }
