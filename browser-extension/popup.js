document.getElementById('connect').addEventListener('click', async () => {
  const button = document.getElementById('connect');
  const status = document.getElementById('status');
  button.disabled = true;
  status.setAttribute('role', 'status');
  status.textContent = 'Verifying your account with local Flow2API. Keep this popup open…';
  try {
    const account = await flowConnector.connect(document.getElementById('code').value);
    document.getElementById('code').value = '';
    status.textContent = `${account.email} is connected. You can return to Bang Story or Flow2API.`;
  } catch (error) {
    status.setAttribute('role', 'alert');
    // Network and extension API errors can contain request details; show only our fixed messages.
    status.textContent = error instanceof FlowConnectorError ? error.message : 'Could not connect to local Flow2API. Keep the app running, check extension permissions, and create a fresh pairing code.';
  } finally { button.disabled = false; }
});
