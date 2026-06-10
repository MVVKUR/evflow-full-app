import { useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router';
import { EVDriverContainer } from '../ev_driver/EVDriverContainer';
import { LoginScreen } from '../login/LoginScreen';
import { ProfileSelectionScreen } from '../profile_selection/ProfileSelectionScreen';
import { RegistrationScreen } from '../registration/RegistrationScreen';
import { ScanSpkluScreen, InitializeChargingScreen, TransactionSuccessScreen, ChargingStatusScreen, ChargingSuccessfulScreen } from '../charging_flow';
import type { UserRole } from '../profile_selection/types';

export function AppRoutes() {
  const [selectedRole, setSelectedRole] = useState<UserRole>('driver');

  return (
    <Routes>
      <Route path="/" element={<LoginRoute />} />
      <Route
        path="/profile-selection"
        element={<ProfileSelectionRoute selectedRole={selectedRole} onSelectRole={setSelectedRole} />}
      />
      <Route path="/register" element={<RegistrationRoute />} />
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

function RegistrationRoute() {
  const navigate = useNavigate();

  return (
    <RegistrationScreen
      onBack={() => navigate('/')}
      // onBack={() => navigate('/profile-selection')}
      onLogin={() => navigate('/')}
      onRegister={() => navigate('/ev-driver')}
    />
  );
}
