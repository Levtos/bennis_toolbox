# Release-Prozess

Diese Checkliste gilt für jedes veröffentlichte Toolbox-Release.

## Versioning

- Patch-Release (`0.3.x`): Bugfixes, Doku, kleine UX-Korrekturen, keine
  neuen Modul-Contracts.
- Minor-Release (`0.x.0`): neues READY-Modul, relevante Service-/Entity-
  Änderungen oder größere UX-Erweiterungen.
- Major-Release (`x.0.0`): brechende Änderungen an Config-Entries,
  Services, WebSockets oder Storage.

## Checklist

1. `custom_components/bennis_toolbox/manifest.json` aktualisieren.
2. `CHANGELOG.md` mit nutzerrelevanten Änderungen, Fixes, Tests und
   bekannten Einschränkungen aktualisieren.
3. Betroffene Doku unter `docs/` und die Modul-Status-Tabelle in
   `README.md`.
4. Komplette Testsuite ausführen:

   ```bash
   python -m pytest -q
   ```

5. Commit mit `chore: release vX.Y.Z`.
6. Annotierten Tag erstellen und pushen:

   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin main
   git push origin vX.Y.Z
   ```

7. GitHub-Release aus dem passenden `CHANGELOG.md`-Abschnitt erstellen.
8. Über HACS auf einer Home-Assistant-Testinstanz installieren oder neu
   herunterladen, HA neu starten und Logs auf neue harte Fehler prüfen.

## Changelog-Regeln

- Zuerst für HA-Nutzer schreiben, nicht nur für Entwickler.
- Modul-IDs nennen, wenn eine Änderung ein konkretes Modul betrifft.
- Bugfixes konkret halten: was war kaputt, was ist jetzt abgesichert
  oder geändert.
- Bekannte Einschränkungen nennen, wenn ein Modul bewusst Stub bleibt
  oder ein Feature bewusst verschoben wurde.
