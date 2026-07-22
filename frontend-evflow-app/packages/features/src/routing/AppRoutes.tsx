import { useState } from 'react';
import { Navigate, Route, Routes, useNavigate, useLocation } from 'react-router';
import { EVDriverContainer } from '../ev_driver/EVDriverContainer';
import { LoginScreen } from '../login/LoginScreen';
import { QuickLoginScreen } from '../login/QuickLoginScreen';
import { ResetPasswordScreen } from '../login/ResetPasswordScreen';
import { VehicleSelectScreen } from '../onboarding/VehicleSelectScreen';
import { ConnectorSelectScreen } from '../onboarding/ConnectorSelectScreen';
import { ProfileSelectionScreen } from '../profile_selection/ProfileSelectionScreen';
import { RegistrationScreen } from '../registration/RegistrationScreen';
import { ScanSpkluScreen, InitializeChargingScreen, TransactionSuccessScreen, ChargingStatusScreen, ChargingSuccessfulScreen } from '../charging_flow';
import type { UserRole } from '../profile_selection/types';

export function AppRoutes() {
  const [selectedRole, setSelectedRole] = useState<UserRole>('driver');

  return (
    <Routes>
      <Route path="/" element={<QuickLoginScreen />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/onboarding/vehicle" element={<VehicleSelectScreen />} />
      <Route path="/onboarding/connector" element={<ConnectorSelectScreen />} />
      <Route
        path="/profile-selection"
        element={<ProfileSelectionRoute selectedRole={selectedRole} onSelectRole={setSelectedRole} />}
      />
      <Route path="/register" element={<RegistrationRoute />} />
      <Route path="/reset-password" element={<ResetPasswordRoute />} />
      <Route path="/ev-driver" element={<Navigate replace to="/ev-driver/map" />} />
      <Route path="/ev-driver/wallet/topup" element={<EVDriverContainer />} />
      <Route path="/ev-driver/wallet/topup/success" element={<EVDriverContainer />} />
      <Route path="/ev-driver/:tab" element={<EVDriverContainer />} />
      <Route path="/charging-flow/scan" element={<ScanSpkluScreen />} />
      <Route path="/charging-flow/initialize" element={<InitializeChargingScreen />} />
      <Route path="/charging-flow/success" element={<TransactionSuccessScreen />} />
      <Route path="/charging-flow/status" element={<ChargingStatusScreen />} />
      <Route path="/charging-flow/successful" element={<ChargingSuccessfulScreen />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}

function LoginRoute() {
  const navigate = useNavigate();

  return <LoginScreen 
    onLogin={() => navigate('/ev-driver')} 
    onRegister={() => navigate('/register')} 
    // onRegister={() => navigate('/profile-selection')} 
  />;
}

type ProfileSelectionRouteProps = {
  selectedRole: UserRole;
  onSelectRole: (role: UserRole) => void;
};

function ProfileSelectionRoute({ selectedRole, onSelectRole }: ProfileSelectionRouteProps) {
  const navigate = useNavigate();

  return (
    <ProfileSelectionScreen
      selectedRole={selectedRole}
      onBack={() => navigate('/')}
      onContinue={() => navigate('/register')}
      onSelectRole={onSelectRole}
    />
  );
}

function tokenFromSearch(search: string): string | null {
  const match = /[?&]token=([^&]+)/.exec(search || '');
  return match ? decodeURIComponent(match[1]) : null;
}

function ResetPasswordRoute() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <ResetPasswordScreen
      token={tokenFromSearch(location.search)}
      onBackToLogin={() => navigate('/login')}
    />
  );
}

function RegistrationRoute() {
  const navigate = useNavigate();

  return (
    <RegistrationScreen
      onBack={() => navigate('/login')}
      // onBack={() => navigate('/profile-selection')}
      onLogin={() => navigate('/login')}
      onRegister={() => navigate('/ev-driver')}
    />
  );
}
