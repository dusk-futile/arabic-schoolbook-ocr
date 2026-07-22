# Windows installation

1. Extract `ArabicSchoolbookOCR-v0.1.0-alpha-windows.zip` to a normal writable folder.
2. Open PowerShell in that folder.
3. Install the local-only application:

   ```powershell
   powershell -ExecutionPolicy Bypass -File install_windows.ps1
   ```

   To install the optional Azure and Gemini client libraries as well:

   ```powershell
   powershell -ExecutionPolicy Bypass -File install_windows.ps1 -Cloud
   ```

4. Double-click `start_windows.bat` or run it from a terminal.
5. Open `http://127.0.0.1:8000` if the browser does not open automatically.

Local mode requires no credentials and sends no page or crop outside the computer. Cloud capabilities require a key, an enabled capability, explicit job consent, and page scope.

The first local Paddle run downloads the audited inference models recorded in `MODEL_SUPPORT.md`. No training dataset is downloaded.
